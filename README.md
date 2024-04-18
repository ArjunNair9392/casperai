# casperai

#### PostGRESQL

# Build the Docker image
docker build -t my_postgres:latest .

# Run the Docker container
docker run -p 5432:5432 my_postgres:latest


###Preprocess
# Build the Docker image
docker build -t upload_service .

# Run the Docker container
docker run -e OPENAI_API_KEY='' -e PINECONE_API_KEY='' -e PINECONE_API_ENV='gcp-starter' -p 8080:8080 upload_service


###Chat
# Build the Docker image
docker build -t chat_service .

# Run the Docker container
docker run -e OPENAI_API_KEY='' -e PINECONE_API_KEY='' -e PINECONE_API_ENV='gcp-starter' -p 8080:8080 chat_service

# Tag Image
docker tag chat_service amitdoshi4/chatservice:chatservice0.0.1

docker tag upload-service amitdoshi4/casperai:uploadservice0.0.1

#Push
docker push amitdoshi4/chatservice:chatservice0.0.1 

docker push amitdoshi4/casperai:uploadservice0.0.1 