import glob
import io
import signal
import time
import joblib
import pandas as pd
from scipy.sparse import save_npz
from core import ConversationQA
from streamlit_option_menu import option_menu
import streamlit as st
from dataclasses import dataclass
from typing import Literal
# from streamlit_chat import message
import os
import utils as ut
from pathlib import Path
import base64
from PIL import Image
import sqlite3
from datetime import datetime as dt


yaml_inputs = ut.load_yaml('settings_app.yml')
os.environ["OPENAI_API_KEY"] = yaml_inputs['open_api_key']
lock_key = yaml_inputs['loc']

##########################################################################################
#                                   SQLITE
##########################################################################################
# Create a connection to the SQLite database
# conn = sqlite3.connect('ntt_llm.db')

##########################################################################################
#                                   YAML Inputs
##########################################################################################

parent_path = Path.cwd()
im_1 = yaml_inputs['background']
im_2 = yaml_inputs['side_image']
side_logo = yaml_inputs['side_logo']
back_color = yaml_inputs['back_color']
hover_color = yaml_inputs['hover_color']
select_color = yaml_inputs['select_color']
icon_color = yaml_inputs['icon_color']


dbs_path = os.path.join(os.getcwd(), yaml_inputs['vdb_path'])
model_path = os.path.join(os.getcwd(), yaml_inputs['tf_model_path'])
data_path = os.path.join(os.getcwd(), yaml_inputs['tf_matrix_path'])
know_db_path = os.path.join(os.getcwd(), yaml_inputs['know_db_path'])
#############################################################################################
@st.cache_data
def get_img_as_base64(file):
    with open(file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

img = get_img_as_base64(im_1)
img2 = get_img_as_base64(im_2)

page_bg_img = f"""
<style>
[data-testid="stAppViewContainer"] {{
background-image: url("data:image/png;base64, {img}");
background-size:auto;
}}

[data-testid="stHeader"] {{
background-image: url("data:image/png;base64, {img}");
background-size:auto;
}}

[data-testid="stSidebar"] {{
background-image: url("data:image/png;base64, {img2}");
background-size:auto;
}}

</style>
"""
st.markdown(page_bg_img, unsafe_allow_html=True)

logo = Image.open(side_logo)
st.sidebar.image(logo)

##########################################################################################
#                                   All CSS Fonts
##########################################################################################
st.markdown(""" <style> .font {
        font-size:35px ; text-align: 'center'; font-family: 'Cooper Black'; color: #FF9633;}
        </style> """, unsafe_allow_html=True)

st.markdown(""" <style> .font2 {
        font-size:25px ; font-family: 'Geneva'; color: #FF9633;}
        </style> """, unsafe_allow_html=True)
st.markdown(""" <style> .font3 {
        font-size:25px ; "text-align": "center", font-family: 'Geneva'; color: #FF9633;}
        </style> """, unsafe_allow_html=True)
st.markdown(""" <style> .font4 {
        font-size:16px ; "text-align": "right", font-family: 'Geneva'; color: 'black';}
        </style> """, unsafe_allow_html=True)

##########################################################################################
                                  # Misc Functions
##########################################################################################
# def send_request_subscription_key():
#     user_id = os.getlogin()
#     # outlook = win32.Dispatch('outlook.application')
#     mail = outlook.CreateItem(0)
#     recipients = yaml_inputs['email_list']
#     mail.To = ';'.join(recipients)
#     mail.Subject = f"User: {user_id} subscription key request for Virtual Assist"
#     mail.HTMLBody = f"User: {user_id} is requesting for new subscription key<br><br>&nbsp;<br>"
#     mail.Send()
#     return True


def get_path():
    src_path = st.text_input(label='Enter the path...')
    return src_path


def check_like():
    st.session_state.emoji_like = '+1'

def check_dislike():
    st.session_state.emoji_like = '-1'

def load_css():
    with open("static/styles.css", "r") as f:
        css = f"<style>{f.read()}</style>"
        st.markdown(css, unsafe_allow_html=True)

def get_text():
    input_text = st.text_input("You: ", "", key="input", max_chars=100, )
    # input_text = st.chat_input("You: ")
    print(input_text)
    return input_text


def generate_response(prompt):
    response, flag = qbot.retrieve_response(prompt)
    return response, flag

def create_sources_string(source_urls:set[str]) -> str:
    if not source_urls:
        return ""

    sources_list = list(source_urls)
    # sources_list.sort()
    sources_string = "sources: \n"

    for i, source in enumerate(sources_list):
        if i==len(sources_list)-1:
            sources_string += f"{i+1}. {source}"
        else:
            sources_string += f"{i + 1}. {source} \n"
    return  sources_string


@dataclass
class Message:
    """Class for keeping track of a chat message"""
    origin: Literal["human", "bot"]
    message: str

##########################################################################################
                                  # Headers
##########################################################################################

if 'generated' not in st.session_state:
    st.session_state['generated'] = []


## past stores User's questions
if 'past' not in st.session_state:
    st.session_state['past'] = ['Hi! I am User']

if 'extras_generated' not in st.session_state:
    st.session_state['extras_generated'] = ['Hi! I am Virtual Assist. Let me know how can I assist you?']

if 'references' not in st.session_state:
    st.session_state['references'] = []

if 'emoji_like' not in st.session_state:
    st.session_state.emoji_like = "0"
if 'path' not in st.session_state:
    st.session_state['path']=''

#########################################################################################
                                # Sidebar
#########################################################################################

with st.sidebar:
        choose = option_menu(menu_title=None, options= [ "Chatbot", "Previous Responses","Create Embed-DB", "Creator", "Stop"],
                                 icons= ['house-fill',  "bi-chat-left-text",'bi-database','bi-bricks', 'file-text-fill', 'stop-circle-fill'],
                                 menu_icon="app-indicator", default_index=0,
                                 styles={
                "container": {"padding": "5!important", "background-color": "black"},
                "icon": {"color": icon_color, "font-size": "25px"},
                "nav-link": {"font-size": "15px", "text-align": "left", "margin":"0px",
                             "--hover-color": hover_color, "--text-color":"white",},
                "nav-link-selected": {"background-color": select_color},
            },
            )


def on_click_callback():
    conn = sqlite3.connect('ntt_llm.db')
    c = conn.cursor()
    # Create a table with the specified columns
    c.execute('''CREATE TABLE IF NOT EXISTS new_response_table(
                        query TEXT NOT NULL,
                        response TEXT NOT NULL,
                        sources TEXT,
                        like TEXT)''')


    user_input = st.session_state.user_input
    # faq_db = qbot.get_faq_data(know_db_path)
    ##########################################New Addded Translation Section###############################################
    if lang_proc == "Non-English":
        lang_det, t_user_input = ut.detect_and_translate(user_input)
        print('================================')
        print(lang_det)
    else:
        t_user_input = user_input

    response, flag = generate_response(t_user_input)
    print(response, flag)

    #################################################################################################################

    if flag == 'from faq':
        formatted_response = "1) From FAQ"

        #####################
        if lang_proc == "Non-English":
            t_response = ut.translate_response(response, lang_det)
        else:
            t_response = response
        #####################

        st.session_state['generated'].append(t_response)
        st.session_state['extras_generated'].append(t_response)
        st.session_state['references'] = formatted_response

        st.session_state['past'].append(user_input)
        st.session_state.emoji_like = "0"
        like = st.session_state.emoji_like

        c.execute("INSERT INTO new_response_table (query, response, sources, like) VALUES (?, ?, ?, ?)",
                  (t_user_input, response, formatted_response, like))
        conn.commit()
        st.success('Data inserted successfully!')
        conn.close()
    else:
        sources = set(
            [str(doc.metadata['source']).split('\\')[-1] + '  ' + 'Page#' + str(doc.metadata['page'] + 1) for doc in
             response['source_documents']])
        sources_m = create_sources_string(sources)
        formatted_response = (
            f"{sources_m}"
        )

        #####################
        if lang_proc == "Non-English":
            t_response = ut.translate_response(response.get("answer", ""), lang_det)
        else:
            t_response = response.get("answer", "")
        #####################

        st.session_state['generated'].append(t_response)
        st.session_state['extras_generated'].append(t_response)
        st.session_state['references'] = formatted_response

        st.session_state['past'].append(user_input)
        st.session_state.emoji_like = "0"
        like = st.session_state.emoji_like

        c.execute("INSERT INTO new_response_table (query, response, sources, like) VALUES (?, ?, ?, ?)",
                  (t_user_input, response.get("answer", ""), formatted_response, like))
        conn.commit()
        st.success('Data inserted successfully!')
        conn.close()


def custom_selectbox(options, colors):
    # Create a dictionary to map colors to their respective options
    color_map = {option: color for option, color in zip(options, colors)}

    # Create a selectbox with the options
    selected_option = st.selectbox("Select an option", options)

    # Get the selected option's color
    selected_option_color = color_map[selected_option]

    # Use HTML and CSS to display the selected option with the corresponding color
    colored_option = f'<span style="color:{selected_option_color};">{selected_option}</span>'
    st.markdown(colored_option, unsafe_allow_html=True)


load_css()
##############################################################################################

if (choose == "SOP Creator"):
    txt_file = st.file_uploader(label="Upload text file", type='txt')
    # st.write(txt_file)
    if txt_file:
        query_content = txt_file.read().decode("utf-8")
        # with open(txt_file.name) as f:
        #     content_txt = f.read()
        st.write(query_content)

        but_sop = st.button("Convert to SOP")
        if but_sop:
            response = chat2sop(query_content, token_limit=yaml_inputs['token_limit_chat2sop'])
            output_sop = response['choices'][0]['message']['content']
            st.markdown(output_sop)
            print(output_sop)
            doc = ut.markdown_to_docx(output_sop)
            doc_buffer = io.BytesIO()
            doc.save(doc_buffer)
            doc_buffer.seek(0)

            st.download_button("Download SOP", data=doc_buffer, file_name="sop_doc.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


elif (choose=='Contact'):
    with st.form(key='columns_in_form2',
                 clear_on_submit=True):  # set clear_on_submit=True so that the form will be reset/cleared once it's submitted
        # st.write('Please help us improve!')
        st.markdown('<p class="font2">Innovation Hub</p>', unsafe_allow_html=True)  #  Collect user feedback
        Email = st.text_input(label='Please Enter Your Email')  # Collect user feedback
        Message = st.text_input(label='Please Enter Your Message')  # Collect user feedback
        submitted = st.form_submit_button('Submit')
        if submitted:
            st.write(
                'Thanks for contacting us. We will respond to your questions or inquiries as soon as possible!')


elif (choose=="Chatbot"):
    st.markdown("<h1 style='text-align: center; color: #1E345C;'>Virtual Assist</h1>",
                    unsafe_allow_html=True)

    # st.markdown("<h5 style='text-align: center; color: black;'>Hello...Before we start, can you please select the country and the"
    #             "process you are working for..</h1>",
    #             unsafe_allow_html=True)

    c1, c2, c3 = st.columns([0.3, 0.3, 0.2])

    with c1:
        sel_1_path = os.path.join(dbs_path, '*')
        sel_1 = glob.glob(sel_1_path)
        sel_1 = [x.split('\\')[-1] for x in sel_1]

        # custom_selectbox(options=sel_1, colors=["red", "green", "blue"])
        selected_1 = st.selectbox(label="Select Folder", options=sel_1)

    with c2:
        lang_proc = st.selectbox(label="Select Language", options=['English', 'Non-English'])

    with c3:
        st.write('')
        st.write('')
        path_check = st.button(label='Submit')

    if selected_1:
        vec_name = selected_1+'_vecdb'
        src_path_db = os.path.join(os.getcwd(), yaml_inputs['vdb_path'], selected_1, vec_name)
        # src_path_db = r'"' + src_path_db  + '"'

    if path_check:
        # st.write('working')
        st.write()
        st.session_state['path'] = src_path_db


    if st.session_state.path:
        # st.write(f"Retrieved from {st.session_state.path}")
        qbot = ConversationQA()
        qbot.chat_bot(st.session_state.path, model_path, data_path, know_db_path)
        faq_db = qbot.get_faq_data(know_db_path)
        chat_placeholder = st.container()

        #####################################################################################
        #######################         References PlaceHolder               ################
        # CSS styling
        # Render CSS styling

        a_col, b_col, c_col = st.columns([0.25, 2, 2])
        if len(st.session_state['references']) != 0:
            with b_col:
                like_c, dislike_c, resp = st.columns([0.33, 0.33,0.33])
                with like_c:
                    like = st.button(f"👍", use_container_width=True, on_click=check_like)
                with dislike_c:
                    dislike = st.button(f"👎", use_container_width=True, on_click=check_dislike)
                with resp:
                    dd = f"""<div style='background-color: #e5e5e5; padding: 7px; border-radius: 5px; text-align: center;'>{st.session_state.emoji_like}
                    </div>

                    """
                    st.markdown(dd, unsafe_allow_html=True)
                with st.expander('References', expanded=False):
                    st.write(st.session_state['references'])



        #####################################################################################
        #######################         PromptPlaceHolder               #####################

        prompt_placeholder = st.form("chat-form", clear_on_submit=True)


        with chat_placeholder:
            for user, generated in zip(st.session_state.past, st.session_state.extras_generated):
                div = f"""
                <div class="chat-row row-reverse">
                    <div class="chat-bubble human-bubble">&#8203;{user}</div>
                </div>
                    """
                st.markdown(div, unsafe_allow_html=True)

                div2 = f"""
                            <div class="chat-row">
                                <div class="chat-bubble ai-bubble">&#8203;{generated}</div>
                            </div>
                                """
                st.markdown(div2, unsafe_allow_html=True)


                # st.markdown(f"From user: {user.message} \n\n From Bot: {generated.message}")


        with prompt_placeholder:
            st.markdown("**Chat**")
            cols = st.columns((6, 1))
            cols[0].text_input(
                "Chat",
                value="",
                label_visibility="collapsed",
                key="user_input",
            )
            cols[1].form_submit_button(
                "Submit",
                type="primary",
                on_click=on_click_callback,
            )

        reset = st.button("Clear Chat History", use_container_width=True)

        if reset:
            st.session_state['generated'] = []
            st.session_state['past'] = ['Hi! I am User']
            st.session_state['extras_generated'] = ['Hi! I am Virtual Assist. Let me know how can I assist you?']
            st.session_state['references']=[]
            qbot.clear_chathistory()


elif (choose=="Previous Responses"):
    conn = sqlite3.connect('test_llm.db')
    c = conn.cursor()

    c.execute("SELECT * FROM new_response_table")
    data = c.fetchall()

    # Display the retrieved data in Streamlit
    if data:
        column_names = [description[0] for description in c.description]
        # st.write(type(data))
        new_df = pd.DataFrame(data,columns=column_names)
        st.table(new_df)
    else:
        st.write('No data found in the database.')


elif (choose=="Create Embed-DB"):

    se = st.selectbox(label="Select Option",options=['Embeddings', 'FAQ DB'])
    if se=="Embeddings":
        src_path = get_path()
        if src_path:
            bot = ConversationQA()
            with st.spinner('Creating Embeddings....'):
                vectordb, db_path, chunks = bot.create_embeddings(src_path)
                vectordb.save_local(db_path)
            st.success(f"Successfully created {len(chunks)} chunks, and saved embeddings in this location: {db_path}")
    elif se =='FAQ DB':
        press = st.button("Create FAQ DB")
        if press:
            bot = ConversationQA()
            tf, tfidf_matrix = bot.create_knowledge_base(know_db_path)
            joblib.dump(tf, yaml_inputs['tf_model_path'])
            save_npz(yaml_inputs['tf_matrix_path'], tfidf_matrix)
            st.write(f"Succesfully saved model to {yaml_inputs['tf_model_path']}, and matrix: "
                     f"{yaml_inputs['tf_matrix_path']}")


elif (choose=='Stop'):
    b = st.button('STOP')
    if b:
        pid = os.getpid()
        os.kill(pid, signal.SIGTERM)