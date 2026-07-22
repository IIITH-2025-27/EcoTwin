# EcoTwin

## Project Summary
1. **EcoTwin**
   - **Topic:** Ecosystem Analog Search and Forecasting Using Geospatial Foundation Models
   - **Description:** Develops an AI-powered ecosystem analog search and forecasting system that uses geospatial foundation model embeddings to identify ecosystems with similar structural and environmental characteristics.

## RUN Project

## 1. Create and activate a virtual environment
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate



## 2.1 RUN pgAdmin (Database)

## 2.2 RUN Backend

Start the API server

```bash
cd backend

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

```

## 3. RUN Frontend

```bash

npm run dev

```

## USEFULL Commands
 ==> Remove All empty folders
 ```
 find . -type d -empty -delete
 ```