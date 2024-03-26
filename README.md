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
docker run -p 8080:8080 upload_service
