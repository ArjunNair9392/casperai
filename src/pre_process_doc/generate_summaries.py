from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

import os
import base64
import shutil

# Load environment variables
load_dotenv()

def generate_text_and_table_summaries(texts, tables, summarize_texts=False):
    """
    Generate summaries of text elements.
    """
    # Prompt template
    prompt_text = """You are an assistant tasked with summarizing tables and text for retrieval. \
    These summaries will be embedded and used to retrieve the raw text or table elements. \
    Give a very detailed summary of the table or text such that when a user asks any question \
    about the table or text, we should be able to derive the answer from the table or text summary. \
    Table or text: {element} """
    prompt = ChatPromptTemplate.from_template(prompt_text)

    def summarize_text_tables_with_page_number(text_tables_with_page_number):
        text_tables, page_number = text_tables_with_page_number
        return {"element": text_tables, "page_number": page_number}
    
    # Initialize text and table summaries
    text_summaries = []
    table_summaries = []
    
    # Summarize texts
    if texts and summarize_texts:
        model = ChatOpenAI(temperature=0, model="gpt-4-vision-preview", openai_api_key=os.getenv("OPENAI_API_KEY"))
        summarize_chain = summarize_text_tables_with_page_number | prompt | model | StrOutputParser()
        text_summaries = summarize_chain.batch(texts, {"max_concurrency": 1})
    elif texts:
        text_summaries = texts
    
    # Summarize tables
    if tables:
        model = ChatOpenAI(temperature=0, model="gpt-4-vision-preview", openai_api_key=os.getenv("OPENAI_API_KEY"))
        summarize_chain = summarize_text_tables_with_page_number | prompt | model | StrOutputParser()
        table_summaries = summarize_chain.batch(tables, {"max_concurrency": 1})

    return text_summaries, table_summaries

def encode_image(image_path):
    """Encode image to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def image_summarize(img_base64, prompt):
    """Generate summary for an image."""
    chat = ChatOpenAI(model="gpt-4-vision-preview", max_tokens=1024, openai_api_key=os.getenv("OPENAI_API_KEY"))

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
    """Delete folder and its contents."""
    folder_path = os.path.join(os.path.dirname(__file__), folder_name)

    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            print(f"Folder deleted: {folder_path}")
        except Exception as e:
            print(f"Error deleting folder: {e}")
    else:
        print(f"Folder does not exist: {folder_path}")

def generate_img_summaries(path):
    """
    Generate summaries and base64 encoded strings for images.
    """
    img_base64_list = []
    image_summaries = []
    folder_to_delete = "figures"

    # Prompt for image summarization
    prompt = """You are an assistant tasked with summarizing images for retrieval. \
    These summaries will be embedded and used to retrieve the raw image. \
    Give a very detailed summary of the image such that when a user asks any question \
    about the image, we should be able to derive the answer from the image summary. """

    # Process each image
    for img_file in sorted(os.listdir(path)):
        if img_file.endswith(".jpg"):
            img_path = os.path.join(path, img_file)
            base64_image = encode_image(img_path)
            img_base64_list.append(base64_image)
            image_summaries.append(image_summarize(base64_image, prompt))

    delete_folder_relative(folder_to_delete)
    return img_base64_list, image_summaries
