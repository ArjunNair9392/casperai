from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

import time
import os
import base64
import shutil


# Generate summaries of text elements
def generate_text_and_table_summaries(texts, tables, summarize_texts=False):
    load_dotenv()
    """
    Summarize text elements
    texts: List of str
    tables: List of panda dataframes
    summarize_texts: Bool to summarize texts
    """

    # Prompt
    prompt_text = """You are an assistant tasked with summarizing tables and text for retrieval. \
    These summaries will be embedded and used to retrieve the raw text or table elements. \
    Give a very detailed summary of the table or text such that when a user asks any question \
    about the table or text, we should be able to derive the answer from the table or text summary. \
    Table or text: {element} """
    prompt = ChatPromptTemplate.from_template(prompt_text)

    # Text summary chain
    model = ChatOpenAI(temperature=0, model="gpt-4", openai_api_key=os.environ["OPENAI_API_KEY"])
    summarize_chain = {"element": lambda x: x} | prompt | model | StrOutputParser()
    # Initialize empty summaries
    text_summaries = []
    table_summaries = []
    print(len(texts))

    # Apply to text if texts are provided and summarization is requested
    if texts and summarize_texts:
        text_summaries = summarize_chain.batch(texts, {"max_concurrency": 1})
    elif texts:
        text_summaries = texts
    # Apply to tables if tables are provided
    if tables:
        table_summaries = summarize_chain.batch(tables, {"max_concurrency": 1})


    return text_summaries, table_summaries

def encode_image(image_path):
    """Getting the base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def image_summarize(img_base64, prompt):
    """Make image summary"""
    chat = ChatOpenAI(model="gpt-4-vision-preview", max_tokens=1024, openai_api_key=os.environ["OPENAI_API_KEY"])

    msg = chat.invoke(
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
                    },
                ]
            )
        ]
    )
    return msg.content

def delete_folder_relative(folder_name):
    folder_path = os.path.join(os.path.dirname(__file__), folder_name)

    if os.path.exists(folder_path):
        try:
            # Use shutil.rmtree() to delete the folder and its contents
            shutil.rmtree(folder_path)
        except Exception as e:
            print(f"Error deleting folder: {e}")
    else:
        print(f"Folder does not exist: {folder_path}")

def generate_img_summaries(path):

    """
    Generate summaries and base64 encoded strings for images
    path: Path to list of .jpg files extracted by Unstructured
    """

    # Store base64 encoded images
    img_base64_list = []

    # Store image summaries
    image_summaries = []

    # Delete the figures folder after it has been converted base64
    folder_to_delete = "figures"

    # Prompt
    prompt = """You are an assistant tasked with summarizing images for retrieval. \
    These summaries will be embedded and used to retrieve the raw image. \
    Give a very detailed summary of the image such that when a user asks any question \
    about the image, we should be able to derive the answer from the image summary. """

    # Apply to images
    for img_file in sorted(os.listdir(path)):
        if img_file.endswith(".jpg"):
            img_path = os.path.join(path, img_file)
            base64_image = encode_image(img_path)
            img_base64_list.append(base64_image)
            image_summaries.append(image_summarize(base64_image, prompt))

    delete_folder_relative(folder_to_delete)
    return img_base64_list, image_summaries