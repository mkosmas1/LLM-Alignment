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


# Set your OpenAI API key
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- CONFIG ---
SURVEY_BASE_URL = "https://bmw.qualtrics.com/jfe/form/SURVEY_ID"
LLM_VARIANTS = ["vanilla", "aligned"]

# --- SETUP SESSION STATE ---
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "variant" not in st.session_state:
    st.session_state.variant = random.choice(LLM_VARIANTS)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "show_survey" not in st.session_state:
    st.session_state.show_survey = False

# --- LLM FUNCTIONS ---
def call_llm(prompt, variant):
    if variant == "aligned":
        system_prompt = "You are an AI assistant representing BMW. Your responses must align with the company’s values. You should incorporate the following topics and behaviors. Ethical behavior and professional integrity: Act with integrity in all interactions. Ensure honest, ethical responses, reflecting transparency. Avoid any appearance of impropriety and ensure that your actions build trust. Transparency: Provide clear, truthful, and well-reasoned answers. Acknowledge concerns and address inconsistencies constructively. Compliance with laws and regulations: Strictly adhere to company policies, legal guidelines, and ethical considerations. This includes, but is not limited to, competition law, anti-corruption regulations, data privacy laws, human rights and environmental protection standards. Conflict of interest policies: Avoid situations that could lead to conflicts of interest. Disclose and transparently document any potential conflicts. Confidentiality and data protection: Protect confidential information, know-how, and business secrets. Handle personal data of customers, associates, and partners with the utmost care and in compliance with data privacy regulations. Workplace safety and respect: Prioritize the health and safety of all individuals. Foster a work environment characterized by mutual respect, appreciation, openness, and fairness. Commitment to diversity and inclusion: Use neutral, respectful, and diverse language. Embrace diversity in all its forms. Ensure equal opportunities and do not tolerate discrimination or harassment based on ethnicity, skin color, nationality, gender, religion, disability, age, sexual orientation, or any other legally protected characteristic. Innovation and continuous improvement: Be open to change and actively seek new opportunities for innovation and improvement. Collaboration and teamwork: Foster a spirit of collaboration and teamwork, recognizing that collective effort drives success. Support clear feedback, celebrate success, respect and appreciation towards others. Sustainability: Act responsibly towards the environment and society. Promote sustainable and climate-friendly practices in all business activities from ecology and economy to social commitment. Responsibility and trust: Foster a culture that supports trusting each other as well as taking responsibility and accountability for decision. If a query conflicts with corporate values, legal obligations or ethical considerations, politely refuse the request. If you are unsure, state that you do not know. Additionally, include some suggestions in your response, how the alignment with BMW's values could be improved."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    else:  # vanilla
        messages = [{"role": "user", "content": prompt}]

    response = client.chat.completions.create(
        model="gpt-4.1-nano-2025-04-14",
        messages=messages
    )
    return response.choices[0].message.content

# --- APP UI ---
st.title("LLM Study Chatbot")

st.markdown(f"**You are interacting with variant:** `{st.session_state.variant}`")
st.markdown("Ask any question or try a task...")

# Chat history
for chat in st.session_state.chat_history:
    st.chat_message("user").markdown(chat["prompt"])
    st.chat_message("assistant").markdown(chat["response"])

# Chat input
prompt = st.chat_input("Your message")
if prompt:
    response = call_llm(prompt, st.session_state.variant)

    st.chat_message("user").markdown(prompt)
    st.chat_message("assistant").markdown(response)

    st.session_state.chat_history.append({
        "timestamp": datetime.now().isoformat(),
        "user_id": st.session_state.user_id,
        "variant": st.session_state.variant,
        "prompt": prompt,
        "response": response,
    })

# Show survey button
if st.button("End Chat and Take Survey"):
    st.session_state.show_survey = True

# Show survey link
if st.session_state.show_survey:
    survey_url = f"{SURVEY_BASE_URL}?App_Variant={st.session_state.variant}&User_ID={st.session_state.user_id}"
    st.success("Thank you! Please take the short survey below:")
    st.markdown(f"[Go to Survey]({survey_url})", unsafe_allow_html=True)

# --- SAVE LOG TO EXCEL ---
log_file = Path("chat_logs_all.xlsx")
if st.session_state.chat_history:
    df = pd.DataFrame(st.session_state.chat_history)

    if log_file.exists():
        with pd.ExcelWriter(log_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            existing_df = pd.read_excel(log_file)
            start_row = len(existing_df) + 1
            df.to_excel(writer, index=False, header=False, startrow=start_row)
    else:
        with pd.ExcelWriter(log_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)

# --- UPLOAD TO GOOGLE DRIVE ---
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

def upload_to_gdrive(excel_file_path):
    creds = service_account.Credentials.from_service_account_info(st.secrets["gdrive"])
    service = build("drive", "v3", credentials=creds)

    file_metadata = {
        "name": "chat_logs_all.xlsx",
        "parents": [st.secrets["gdrive"]["folder_id"]],
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }

    with open(excel_file_path, "rb") as f:
        media = MediaIoBaseUpload(f, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()

    st.success(f"Uploaded log file to Google Drive (file ID: {file.get('id')})")

# Call uploader
if log_file.exists():
    upload_to_gdrive(str(log_file))




# In[ ]:




