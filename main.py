from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np

# RUN: uvicorn main:app --reload

app = FastAPI(title="Kazakhmys Инциденты ВОЛС - Аналитическая Панель")

templates = Jinja2Templates(directory="templates")

def load_data():
    df = pd.read_excel('data/sap-btp-omnitracker-data.xlsx', sheet_name='Лист2', engine='openpyxl')
    
    # Преобразование временных столбцов
    time_cols = [col for col in df.columns if 'время' in col.lower()]
    for col in time_cols:
        df[col] = pd.to_datetime(df[col], format="%d.%m.%Y %H:%M:%S")
    
    # Заполнение пропущенных значений
    df = df.apply(lambda col: col.fillna(-1) if col.dtype.kind in 'biufc' else col.fillna("Неизвестно"))
    
    # Добавление расчетных полей
    df['Year-Month'] = df['Время_регистрации_(создания)'].dt.to_period('M').astype(str)
    df['Тип инцидента (IN/OUT)'] = df['Причина инцидента'].apply(
        lambda x: 'Внутренние' if x in ('Повреждение', 'Обрыв линии') else 'Внешние'
    )
    
    return df

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

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
        color_discrete_sequence=['pink']
    )
    fig.update_layout(xaxis_tickangle=-45)
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
        color_discrete_sequence=['skyblue']
    )
    fig.update_layout(xaxis_tickangle=-45)
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
        color_discrete_sequence=['skyblue']
    )
    fig.update_layout(xaxis_tickangle=-45)
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
    fig.update_layout(xaxis_tickangle=-45)
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