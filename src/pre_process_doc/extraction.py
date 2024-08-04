# Python Libraries
import os
import camelot

from langchain.text_splitter import CharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai.embeddings import OpenAIEmbeddings
from unstructured.partition.pdf import partition_pdf
from logging_config import logger
from PIL import Image

# Import local python files
from generate_summaries import generate_text_and_table_summaries, generate_img_summaries
from retriever import create_multi_vector_retriever

# TODO: Amit to replace with Adobe
# Extract elements from PDF
def extract_pdf_elements(file_path, file_name):
    """
    Extract images, tables, and chunk text from a PDF file.
    path: File path, which is used to dump images (.jpg)
    fname: File name
    """
    return partition_pdf(
        filename=file_path + file_name,
        extract_images_in_pdf=True,
        infer_table_structure=True,
        chunking_strategy="by_title",
        max_characters=4000,
        new_after_n_chars=3800,
        combine_text_under_n_chars=2000,
        image_output_dir_path=file_path,
    )


# Categorize elements by type
def extract_texts(raw_pdf_elements):
    """
    Categorize extracted elements from a PDF into tables and texts.
    raw_pdf_elements: List of unstructured.documents.elements
    """
    logger.info(f"Extracting text")
    texts = []
    for element in raw_pdf_elements:
        if "unstructured.documents.elements.CompositeElement" in str(type(element)):
            texts.append(str(element))
    return texts


def extract_tables(fpath, fname):
    logger.info(f"Extracting tables")
    # Use camelot to read tables from the PDF
    tables = camelot.read_pdf(fpath + fname, flavor='stream', pages='all')
    dataframes = [table.df for table in tables]

    logger.info(f"Extracting tables complete")
    return dataframes


def extract_images(img_path):
    images = []
    # iterate over files in directory
    logger.info(f"Extracting images")
    if os.path.exists(img_path):
        for filename in os.listdir(img_path):
            if filename.endswith(".jpg"):
                img = Image.open(os.path.join(img_path, filename))
                images.append(img)
    logger.info(f"Extracting images complete")
    return images


def semantic_chunking_texts(texts):
    semantic_chunker = SemanticChunker(OpenAIEmbeddings(model="text-embedding-3-small"),
                                       breakpoint_threshold_type="percentile")
    semantic_chunks = semantic_chunker.create_documents(texts)
    semantic_text_chunks = [doc.page_content for doc in semantic_chunks]
    return semantic_text_chunks


def convert_tables_to_json(tables):
    logger.info(f"Converting tables to json")
    json_tables = [df.to_json(orient='records') for df in tables]
    return json_tables


def process_pdf(file_path, file_name, index_name, file_id):
    # File path
    logger.info(f"In process pdf for file '{file_name}'")
    img_path = "figures/"
    # Get elements
    raw_pdf_elements = extract_pdf_elements(file_path, file_name)
    # Get text, tables
    texts = extract_texts(raw_pdf_elements)
    tables = extract_tables(file_path, file_name)
    images = extract_images(img_path)
    chunked_texts = semantic_chunking_texts(texts)

    # Get text, table summaries
    text_summaries, table_summaries = generate_text_and_table_summaries(
        chunked_texts, tables, summarize_texts=True
    )

    # Image summaries
    img_base64_list, image_summaries = generate_img_summaries(img_path)
    json_tables = convert_tables_to_json(tables)

    logger.info(f"PDF extraction complete for file '{file_name}'")
    # Create retriever
    retriever_multi_vector_img = create_multi_vector_retriever(
        text_summaries,
        chunked_texts,
        table_summaries,
        json_tables,
        image_summaries,
        img_base64_list,
        index_name,
        file_id
    )
