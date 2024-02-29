from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from PIL import Image

import io
import re
import base64
import pandas as pd



def looks_like_base64(sb):
    """Check if the string looks like base64"""
    return re.match("^[A-Za-z0-9+/]+[=]{0,2}$", sb) is not None


def is_image_data(b64data):
    """
    Check if the base64 data is an image by looking at the start of the data
    """
    image_signatures = {
        b"\xFF\xD8\xFF": "jpg",
        b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A": "png",
        b"\x47\x49\x46\x38": "gif",
        b"\x52\x49\x46\x46": "webp",
    }
    try:
        header = base64.b64decode(b64data)[:8]  # Decode and get the first 8 bytes
        for sig, format in image_signatures.items():
            if header.startswith(sig):
                return True
        return False
    except Exception:
        return False


def resize_base64_image(base64_string, size=(128, 128)):
    """
    Resize an image encoded as a Base64 string
    """
    # Decode the Base64 string
    img_data = base64.b64decode(base64_string)
    img = Image.open(io.BytesIO(img_data))

    # Resize the image
    resized_img = img.resize(size, Image.LANCZOS)

    # Save the resized image to a bytes buffer
    buffered = io.BytesIO()
    resized_img.save(buffered, format=img.format)

    # Encode the resized image to Base64
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def split_image_text_types(docs):
    """
    Split base64-encoded images and texts
    """
    b64_images = []
    texts = []
    table_df = []
    for doc in docs:
    # Check if the document is of type Document and extract page_content if so
      if isinstance(doc, Document):
            doc = doc.page_content
      if isinstance(doc, pd.DataFrame):
          table_df.append(doc)
      elif looks_like_base64(doc) and is_image_data(doc):
          doc = resize_base64_image(doc, size=(1300, 600))
          b64_images.append(doc)
      else:
          texts.append(doc)
    return {"images": b64_images, "texts": texts, "tables": table_df}


def img_prompt_func(data_dict):
    """
    Join the context into a single string
    """

    formatted_texts = "\n".join(data_dict["context"]["texts"])
    messages = []


    # Adding table(s) to the messages if present
    table_message = ""
    if data_dict["context"]["tables"]:
        for table in data_dict["context"]["tables"]:
            df = pd.DataFrame(table)
            table_message += str(df)
            table_message += "\n"  # add a newline between tables

    # Append table messages to formatted_texts
    if table_message:
        formatted_texts += "\nTables:\n" + table_message

    # Adding image(s) to the messages if present
    if data_dict["context"]["images"]:
        for image in data_dict["context"]["images"]:
            image_message = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            }
            messages.append(image_message)

    # Adding the text for analysis
    text_message = {
        "type": "text",
        "text": (
            "You are a helpful chat bot.\n"
            "You will be given a mixed of text, tables, and image(s).\n"
            "Use this information to answer the user question. \n"
            "Only limit your knowledge to context set here. \n"
            f"User-provided question: {data_dict['question']}\n\n"
            "Text and / or tables context:\n"
            f"{formatted_texts}"
        ),
    }
    messages.append(text_message)
    return [HumanMessage(content=messages)]
def multi_modal_rag_chain(retriever):
    """
    Multi-modal RAG chain
    """

    # Multi-modal LLM
    model = ChatOpenAI(temperature=0, model="gpt-4-vision-preview", max_tokens=1024)

    # RAG pipeline
    chain = (
        {
            "context": retriever | RunnableLambda(split_image_text_types),
            "question": RunnablePassthrough(),
        }
        | RunnableLambda(img_prompt_func)
        | model
        | StrOutputParser()
    )

    return chain