import os
from typing import Any
import pandas as pd
from pathlib import Path
from langchain.chains import RetrievalQA
from singleton_decorator import singleton
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from utils import load_doc_from_dir
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import joblib

from langchain.prompts import (
SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
)
from scipy.sparse import load_npz


@singleton
class ConversationQA:
    def __init__(self, search_doc_limit=4):
        self.search_doc_limit = search_doc_limit
        self.chat_history = []


    def chat_bot(self, vecdb_path, model_path, data_path, know_db_path, threshold:float=0.9):
        self.threshold = threshold
        self.tfidf_model = joblib.load(model_path)
        self.tfidf_mat = load_npz(data_path)
        self.faq = self.get_faq_data(know_db_path)
        self.vecdb_path = vecdb_path
        self.vectordb = FAISS.load_local(self.vecdb_path, embeddings=OpenAIEmbeddings())

        system_msg_template = SystemMessagePromptTemplate.from_template(r"""
        You are a chatbot that answers questions from information provided in the document i will be passing to you. 
        When you are asked a question, follow these rules:
        1) Generate a number of additional questions as required that would help more accurately answer the question
        2) Answer those questions yourself and combine the answers to the individual questions to produce the final answer to the overall question.
        3) If you are still not clear, then respond saying:
        "Hey, I am not sure about the answer to your query based on the document chunks passed over to me."
        4) Handle general greetings without searching in the document. 
        5) If the query contains hi, Hi, Bye, Hello then ignore the chat history and just reply with the following fixed reply
        "Hi, I am happy to assist you"
        {context}
        """)

        human_msg_template = HumanMessagePromptTemplate.from_template(template = "{question}")

        prompt_template = ChatPromptTemplate.from_messages(
            [system_msg_template, human_msg_template]
        )

        self.qa = ConversationalRetrievalChain.from_llm(
            ChatOpenAI(temperature=0.2, model_name = "gpt-3.5-turbo"),
            self.vectordb.as_retriever(search_kwargs = {'k':self.search_doc_limit}),
            return_source_documents = True,
            verbose=False,
            combine_docs_chain_kwargs={"prompt":prompt_template}
        )

    def create_embeddings(self, src_path):
        src_split = src_path.split('\\')
        vec_db_name = src_split[-1] +'_vecdb'
        documents = load_doc_from_dir(src_path)
        vectordb = FAISS.from_documents(documents, embedding=OpenAIEmbeddings())
        db_path = "vector_databases" + '/' +src_split[-1] + '/' +vec_db_name
        return vectordb, db_path, documents

    def create_knowledge_base(self, faq_path):
        faq = self.get_faq_data(faq_path)
        corpus = faq['FAQ'].to_list()
        tf = TfidfVectorizer(stop_words='english')
        tfidf_matrix = tf.fit_transform(corpus)
        return tf, tfidf_matrix

    def retrieve_from_knowledge_base(self, query: str):
        query_mat = self.tfidf_model.transform([query])
        pw_sim = cosine_similarity(query_mat, self.tfidf_mat)
        thresh = pw_sim.max()
        ind = pw_sim.argmax()
        ref_ans = self.faq.loc[ind]['Answer']
        return thresh, ref_ans


    def retrieve_response(self, query: str):
        flag = 'from chatgpt'
        thresh, ref_ans = self.retrieve_from_knowledge_base(query)
        if thresh > 0.9:
            print("----------------------------------------------------------------")
            print('Answer taken from knowledge base')
            flag = 'from faq'
            self.clear_chathistory()
            # self.chat_history.append((query, ref_ans))
            return ref_ans, flag
        else:
        # vectordbkwargs = {"search_distance": 0.6}
            print("----------------------------------------------------------------")
            # print(self.chat_history)
            print("----------------------------------------------------------------")

            result = self.qa({"question": query,
                              "chat_history": []})

            self.clear_chathistory()
            # self.chat_history.append((query, result["answer"]))
            # print(result)
            return result, flag

    def clear_chathistory(self):
        self.chat_history = []

    def get_faq_data(self, faq_path):
        faq_path = Path(faq_path)
        paths = []
        for path in faq_path.glob(pattern="*.xlsx"):
            paths.append(path)
        faq = pd.read_excel(paths[0])
        return faq
