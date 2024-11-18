from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import logging
import numpy as np
import os
import shutil
from pathlib import Path

# RUN: uvicorn main:app --reload

app = FastAPI(
    title="Kazakhmys Инциденты ВОЛС - Аналитическая Панель",
    docs_url=None if os.getenv('ENVIRONMENT') == 'production' else '/docs'
)

templates = Jinja2Templates(directory="templates")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_FILE_PATH = DATA_DIR / "sap-btp-omnitracker-data.xlsx"

logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_data(file_path=UPLOAD_FILE_PATH):
    df = pd.read_excel(file_path, sheet_name='Лист2', engine='openpyxl')
    
    time_cols = [col for col in df.columns if 'время' in col.lower()]
    for col in time_cols:
        df[col] = pd.to_datetime(df[col], format="%d.%m.%Y %H:%M:%S", errors='coerce')
    
    df = df.apply(lambda col: col.fillna(-1) if col.dtype.kind in 'biufc' else col.fillna("Неизвестно"))
    
    df['Year-Month'] = df['Время_регистрации_(создания)'].dt.to_period('M').astype(str)
    df['Тип инцидента (IN/OUT)'] = df['Причина инцидента'].apply(
        lambda x: 'Внутренние' if x in ('Повреждение', 'Обрыв линии') else 'Внешние'
    )
    
    return df

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error(f"Error processing request: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"}
    )

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        if not file.filename.endswith('.xlsx'):
            raise HTTPException(status_code=400, detail="Only .xlsx files are allowed")
        
        file_size = 0
        with open(UPLOAD_FILE_PATH, "wb") as buffer:
            while chunk := await file.read(8192):
                file_size += len(chunk)
                if file_size > 10_000_000:  # 10MB limit
                    raise HTTPException(status_code=400, detail="File too large")
                buffer.write(chunk)
        
        try:
            df = pd.read_excel(UPLOAD_FILE_PATH, sheet_name='Лист2', engine='openpyxl')
            required_columns = ['Время_регистрации_(создания)', 'Причина инцидента', 
                              'Местонахождение', 'Производственный объект', 'Тип_запроса']
            if not all(col in df.columns for col in required_columns):
                raise HTTPException(status_code=400, detail="Invalid file format")
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid Excel file format")
        
        return {"message": "File uploaded successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Error uploading file")

@app.get("/api/incidents_by_month")
async def get_incidents_by_month():
    df = load_data()
    monthly_counts = df.groupby('Year-Month').size().reset_index(name='count')
    fig = px.bar(
        monthly_counts,
        x='Year-Month',
        y='count',
        title='Количество инцидентов: распределение по времени',
        labels={'count': 'Количество инцидентов', 'Year-Month': 'Период'},
        color_discrete_sequence=['rgb(59, 130, 246)']
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=50, r=20, t=50, b=100),
        height=400
    )
    return fig.to_json()

@app.get("/api/incident_type_and_reason")
async def get_incident_type_and_reason():
    df = load_data()
    distribution = df.groupby(['Тип инцидента (IN/OUT)', 'Причина инцидента']).size().reset_index(name='count')
    fig = px.bar(
        distribution,
        x='Тип инцидента (IN/OUT)',
        y='count',
        color='Причина инцидента',
        title='Распределение инцидентов по типу и причине',
        labels={'count': 'Количество инцидентов'}
    )
    fig.update_layout(
        margin=dict(l=50, r=20, t=50, b=100),
        height=400
    )
    return fig.to_json()

@app.get("/api/incidents_by_location")
async def get_incidents_by_location():
    df = load_data()
    location_counts = df['Местонахождение'].value_counts().reset_index()
    location_counts.columns = ['Местонахождение', 'count']
    fig = px.bar(
        location_counts,
        x='Местонахождение',
        y='count',
        title='Распределение инцидентов по местоположению',
        labels={'count': 'Количество инцидентов'},
        color_discrete_sequence=['rgb(59, 130, 246)']
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=50, r=20, t=50, b=100),
        height=400
    )
    return fig.to_json()

@app.get("/api/incidents_by_production_object")
async def get_incidents_by_production_object():
    df = load_data()
    object_counts = df['Производственный объект'].value_counts().reset_index()
    object_counts.columns = ['Объект', 'count']
    fig = px.bar(
        object_counts,
        x='Объект',
        y='count',
        title='Распределение инцидентов по производственному объекту',
        labels={'count': 'Количество инцидентов'},
        color_discrete_sequence=['rgb(59, 130, 246)']
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=50, r=20, t=50, b=100),
        height=400
    )
    return fig.to_json()

@app.get("/api/incident_distribution_by_type_and_status")
async def get_incident_distribution_by_type_and_status():
    df = load_data()
    distribution = df.groupby(['Тип_запроса', 'Статус инцидента']).size().reset_index(name='count')
    fig = px.bar(
        distribution,
        x='Тип_запроса',
        y='count',
        color='Статус инцидента',
        title='Распределение инцидентов по типу запроса и статусу',
        labels={'count': 'Количество инцидентов'}
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=50, r=20, t=50, b=100),
        height=400
    )
    return fig.to_json()

@app.get("/api/summary_stats")
async def get_summary_stats():
    df = load_data()
    stats = {
        "total_incidents": len(df),
        "resolved_percentage": (df['Статус запроса'] == '5-Закрыт').mean() * 100,
        "most_common_location": df['Местонахождение'].mode()[0],
        "most_common_type": df['Тип_запроса'].mode()[0]
    }
    return stats