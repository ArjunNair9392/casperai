from unstructured.partition.pdf import partition_pdf
from langchain.text_splitter import CharacterTextSplitter
from PIL import Image
from generate_summaries import generate_text_and_table_summaries, generate_img_summaries
from retriever import create_multi_vector_retriever

import camelot
import os
import fitz

def extract_pdf_elements(file_path, file_name):
    """
    Extracts elements such as images, tables, and chunked text from a PDF file.
    """
    partitions = partition_pdf(
        filename=os.path.join(file_path, file_name),
        extract_images_in_pdf=True,
        infer_table_structure=True,
        chunking_strategy="by_title",
        max_characters=4000,
        new_after_n_chars=3800,
        include_metadata=True,
        combine_text_under_n_chars=2000,
        image_output_dir_path=file_path,
    )

    return partitions

def extract_text(raw_pdf_elements):
    """
    Categorizes extracted elements from a PDF into texts.
    """
    texts_with_page_numbers = []
    for element in raw_pdf_elements:
        if "unstructured.documents.elements.CompositeElement" in str(type(element)):
            text = str(element)
            page_number = element.metadata.page_number
            texts_with_page_numbers.append((text, page_number))
    return texts_with_page_numbers

def extract_tables(file_path, file_name):
    """
    Extracts tables from the PDF using Camelot.
    """
    tables = camelot.read_pdf(os.path.join(file_path, file_name), flavor='stream', pages='all')
    tables_with_page_numbers = [(table.df, table.page) for table in tables]
    return tables_with_page_numbers

def extract_images(image_path):
    """
    Extracts images from a directory.
    """
    images = []
    if os.path.exists(image_path):
        for filename in os.listdir(image_path):
            if filename.endswith(".jpg"):
                img = Image.open(os.path.join(image_path, filename))
                images.append(img)
    return images

def chunk_text(texts_with_page_numbers):
    """
    Chunks texts into smaller segments.
    """
    text_splitter = CharacterTextSplitter.from_tiktoken_encoder(chunk_size=4000, chunk_overlap=0)
    chunks_with_page_numbers = [(chunk, page_number) for text, page_number in texts_with_page_numbers
                                for chunk in text_splitter.split_text(text)]
    return chunks_with_page_numbers

def convert_tables_to_json(tables_with_page_numbers):
    """
    Converts tables to JSON format.
    """
    json_tables = [(df.to_json(orient='records'), page_number) for df, page_number in tables_with_page_numbers]
    return json_tables

def process_pdf(file_path, file_name, index_name):
    """
    Extracts and summarizes elements from a PDF file.
    """
    img_dir_path = "figures/"
    raw_pdf_elements = extract_pdf_elements(file_path, file_name)
    texts_with_page_numbers = extract_text(raw_pdf_elements)
    tables_with_page_numbers = extract_tables(file_path, file_name)
    images = extract_images(img_dir_path)
    chunked_texts = chunk_text(texts_with_page_numbers)

    text_summaries, table_summaries = generate_text_and_table_summaries(
        chunked_texts, tables_with_page_numbers, summarize_texts=True
    )

    img_base64_list, image_summaries = generate_img_summaries(img_dir_path)
    json_tables = convert_tables_to_json(tables_with_page_numbers)

    retriever_multi_vector = create_multi_vector_retriever(
        text_summaries,
        texts_with_page_numbers,
        table_summaries,
        json_tables,
        image_summaries,
        img_base64_list,
        index_name
    )
