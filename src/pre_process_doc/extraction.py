from unstructured.partition.pdf import partition_pdf
from langchain.text_splitter import CharacterTextSplitter
from PIL import Image
from generate_summaries import generate_text_and_table_summaries, generate_img_summaries
from retriever import create_multi_vector_retriever

import camelot
import os

# Extract elements from PDF
def extract_pdf_elements(fpath, fname):
    """
    Extract images, tables, and chunk text from a PDF file.
    path: File path, which is used to dump images (.jpg)
    fname: File name
    """
    return partition_pdf(
        filename=fpath + fname,
        extract_images_in_pdf=False,
        infer_table_structure=True,
        chunking_strategy="by_title",
        max_characters=4000,
        new_after_n_chars=3800,
        combine_text_under_n_chars=2000,
        image_output_dir_path=fpath,
    )

# Categorize elements by type
def extract_texts(raw_pdf_elements):
    """
    Categorize extracted elements from a PDF into tables and texts.
    raw_pdf_elements: List of unstructured.documents.elements
    """
    texts = []
    for element in raw_pdf_elements:
        if "unstructured.documents.elements.CompositeElement" in str(type(element)):
            texts.append(str(element))
    return texts

def extract_tables(fpath, fname):
    # Use camelot to read tables from the PDF
    tables = camelot.read_pdf(fpath+fname, flavor='stream', pages='all')
    dataframes = [table.df for table in tables]

    return dataframes


def extract_images(img_path):
    
    images = []
    # iterate over files in directory
    if os.path.exists(img_path):
        for filename in os.listdir(img_path):
            if filename.endswith(".jpg"):
                img = Image.open(os.path.join(img_path, filename))
                images.append(img)

    return images

def chunkning_texts(texts):
    # Optional: Enforce a specific token size for texts
    text_splitter = CharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=4000, chunk_overlap=0
    )
    joined_texts = " ".join(texts)
    texts_4k_token = text_splitter.split_text(joined_texts)

    return texts_4k_token

def convert_tables_to_json(tables):
    json_tables = [df.to_json(orient='records') for df in tables]
    return json_tables

def extract_summarize_pdf(fpath, fname, indexName):
    # File path
    img_path = "/figures/"
    # Get elements
    raw_pdf_elements = extract_pdf_elements(fpath, fname)
    # Get text, tables
    texts = extract_texts(raw_pdf_elements)
    tables = extract_tables(fpath, fname)
    images = extract_images(img_path)
    texts_4k_token = chunkning_texts(texts)

    # Get text, table summaries
    text_summaries, table_summaries = generate_text_and_table_summaries(
        texts_4k_token, tables, summarize_texts=True
    )

    # Image summaries
    # img_base64_list, image_summaries = generate_img_summaries(img_path)
    img_base64_list = []
    image_summaries = []
    json_tables = convert_tables_to_json(tables)

    # Create retriever
    retriever_multi_vector_img = create_multi_vector_retriever(
        text_summaries,
        texts,
        table_summaries,
        json_tables,
        image_summaries,
        img_base64_list,
        indexName
    )

# if __name__ == "__main__":
#     main()
