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

## 2.2 Install The requrements
```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-ml.txt //only for Local Setup
cd app/ML_models/Prithvi-EO-1.0-100M
pip install -r requirements.txt
```

## 2.3 RUN Backend

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
 1) ==> Remove All empty folders , Run the below command from that specific folder location 
 ```
 find . -type d -empty -delete
 ```

 2) ==> Kill the used port     
 ```
 sudo kill -9 $(sudo lsof -t -i:8000)
 ```

 3) ==> How to run alembic previous script

 s1 : update the alembic version in the db
 ```sql
 UPDATE alembic_version SET version_num = '012';
 ```

 s2 : Run the required script
 ```bash
 alembic upgrade 013
 ```
 Now the head will set to 013, after this you can run the "alembic upgrade head for future scripts"