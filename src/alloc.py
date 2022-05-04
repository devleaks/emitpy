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
cal={}
bays = {}
entries = []

for r in csvdata:
    bay = r["BAY_x"]
    if bay not in bays.keys():
        bid = len(bays) + 1
        bays[bay] = {
            "id": bid,
            "name": bay
        }

    eid = len(entries) + 1
    entries.append({
        "name": '<div>'+r["AIRLINE CODE_x"]+r["FLIGHT NO_x"]+">"+r["AIRLINE CODE_y"]+r["FLIGHT NO_y"]+'</div>',
        "startDate": r['FLIGHT SCHEDULED TIME_x'],
        "endDate": r['FLIGHT SCHEDULED TIME_y'],
        "taskName": r["BAY_x"],
        "status": random.choice(["none", "one", "two", "three"])
    })

cal["Items"] = entries
cal["Sections"] = [k["name"] for k in sorted(bays.values(), key=lambda x: x["name"])]

app = FastAPI()

app.mount("/static", StaticFiles(directory="web/static"), name="static")

templates = Jinja2Templates(directory="web/templates")

@app.get("/")
async def read_item(request: Request):
    return templates.TemplateResponse("alloc.html", {"request": request, "calstr": json.dumps(cal)})

@app.get("/alloc")
async def read_item():
    return JSONResponse(content=cal)
