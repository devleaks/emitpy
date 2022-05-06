from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import csv
import os
import json
import random

filename = os.path.join("..", "data", "managedairport", "OTHH", "flights", "2019_W15_ROTATION_RAW.csv")
file = open(filename, "r")
csvdata = csv.DictReader(file)

bays = {}

for r in csvdata:
    bay = r["BAY_x"]
    if bay not in bays.keys():
        bays[bay] = {
            "measure": bay,
            "data": [],
            "description": [],
            "categories": {
                "11": { "class": "delay11" },
                "00": { "class": "delay00" },
                "10": { "class": "delay10" },
                "01": { "class": "delay01" }
            }
        }
    ontime = float(r['FLIGHT TOTAL DELAY_x']) < 20
    ontime2 = float(r['FLIGHT TOTAL DELAY_x']) < 20
    ontimec = f"{1 if ontime else 0}{1 if ontime2 else 0}"
    bays[bay]["data"].append([r['FLIGHT SCHEDULED TIME_x'], ontimec, r['FLIGHT SCHEDULED TIME_y']])
    bays[bay]["description"].append(f"{r['AIRLINE CODE_x']}{r['FLIGHT NO_x']} ({r['AIRPORT_x']})"
           + f" -> {r['AIRLINE CODE_y']}{r['FLIGHT NO_y']} ({r['AIRPORT_y']})")

bays = dict(sorted(bays.items()))  # sort by key=bay

app = FastAPI()

app.mount("/static", StaticFiles(directory="web/static"), name="static")

templates = Jinja2Templates(directory="web/templates")

@app.get("/")
async def read_item(request: Request):
    return templates.TemplateResponse("visavail.html", {"request": request})

@app.get("/alloc")
async def read_item():
    return JSONResponse(content=list(bays.values()))
